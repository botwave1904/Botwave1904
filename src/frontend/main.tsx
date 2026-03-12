import React from 'react';
import { View, Text, FlatList } from 'react-native';
import create from 'zustand';

interface Vehicle {
  id: string;
  type: string;
  status: string;
  location: { lat: number, lng: number };
}

interface FleetStore {
  vehicles: Vehicle[];
  addVehicle: (vehicle: Vehicle) => void;
}

const useFleetStore = create<FleetStore>((set) => ({
  vehicles: [],
  addVehicle: (vehicle) => set((state) => ({
    vehicles: [...state.vehicles, vehicle]
  }))
}));

const FleetDashboard: React.FC = () => {
  const { vehicles } = useFleetStore();

  return (
    <View>
      <Text>Fleet Commander</Text>
      <FlatList
        data={vehicles}
        renderItem={({ item }) => (
          <View>
            <Text>{item.id} - {item.type}</Text>
            <Text>Status: {item.status}</Text>
          </View>
        )}
        keyExtractor={(item) => item.id}
      />
    </View>
  );
}

export default FleetDashboard;